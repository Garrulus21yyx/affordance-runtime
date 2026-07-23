import asyncio
import json
from dataclasses import dataclass, replace
from typing import Any, Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.adapters.dom import DomAdapter, PageAffordanceModel
from affordance_runtime.adapters.som import SomAdapter
from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    ExecutionReceipt,
    Observation,
    RiskLevel,
    VerifierSpec,
)
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.executors import VisualExecutor, WotExecutor
from affordance_runtime.generalist_planner import GeneralistLMPlanner
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.planning import ContractBuilder, ContractRequirements, PlannerActionKind
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec

T = TypeVar("T", bound=BaseModel)


class StaticObserver:
    def __init__(self, affordance: Affordance) -> None:
        revision = affordance.lease.environment_revision
        snapshot_id = affordance.lease.snapshot_id or "snap-1"
        page_revision = affordance.lease.page_revision or revision
        observation = Observation(
            revision,
            snapshot_id=snapshot_id,
            page_revision=page_revision,
            target_fingerprints={affordance.id: affordance.target_fingerprint},
        )
        model = PageAffordanceModel("surface", "", revision, snapshot_id, page_revision, [affordance], 1, 1)
        self.snapshot = BrowserSnapshot(observation, model)

    def capture(self) -> BrowserSnapshot:
        return self.snapshot


@dataclass
class OneActionPlanner:
    verifier: VerifierSpec

    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope
        if state.receipts:
            return PlannerDecision(done=True, result={"surface": snapshot.affordance_model.affordances[0].surface.value})
        affordance = snapshot.affordance_model.affordances[0]
        contract = ActionContract.from_affordance(
                affordance,
                intent="exercise shared contract path",
                backend=affordance.backend_candidates[0],
                verifier_plan=[self.verifier],
            )
        if affordance.surface.value == "wot":
            contract = replace(contract, idempotency_key="fixture-wot-action", contract_hash="")
        return PlannerDecision(
            contract=contract
        )


class Pointer:
    def click_xy(self, x: int, y: int) -> None:
        self.last_click = (x, y)

    def type_text(self, text: str) -> None:
        self.last_text = text


@dataclass
class GeneralistSurfaceModel:
    provider: str = "fixed"
    model: str = "surface-generalist"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del config
        context = json.loads(messages[-1].content)
        completed = context["latest_outcome"]["verification_status"] == "passed"
        payload = {
            "action_kind": PlannerActionKind.FINISH if completed else PlannerActionKind.ACTIVATE,
            "target_affordance_id": "" if completed else context["affordances"][0]["id"],
            "done": completed,
            "result": {"verified": True} if completed else {},
            "expected_effects": ["shared state enabled"],
        }
        return output_schema.model_validate(payload)


@dataclass
class EvidenceExecutor:
    backend: str
    evidence: dict[str, Any]

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        return ExecutionReceipt(
            contract.id,
            self.backend,
            True,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            evidence=self.evidence,
        )


def test_visual_affordance_uses_task_coordinator_contract_trace_path() -> None:
    affordance = SomAdapter().parse(
        [{"bbox": [10, 10, 20, 20], "label": "Target"}],
        environment_revision="rev-1",
        snapshot_id="snap-1",
    )[0]
    result = asyncio.run(
        RunCoordinator(
            StaticObserver(affordance),
            OneActionPlanner(VerifierSpec("evidence", "action", "visual_click")),
            VisualExecutor(Pointer()),
        ).run(TaskEnvelope("visual-run", "click visual target"))
    )

    assert result.status == RuntimeStep.DONE
    assert result.result == {"surface": "visual"}
    assert "PostconditionPassed" in [node.kind for node in result.trace.nodes]


def test_wot_affordance_uses_task_coordinator_contract_trace_path() -> None:
    td = {
        "id": "lamp",
        "base": "http://fixture",
        "actions": {"turn_on": {"forms": [{"href": "/on", "op": "invokeaction"}]}},
    }
    affordance = WotAdapter().parse(td, environment_revision="rev-1", snapshot_id="snap-1").affordances[0]

    def send(method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        del method, url, kwargs
        return 200, {"power": "on"}

    result = asyncio.run(
        RunCoordinator(
            StaticObserver(affordance),
            OneActionPlanner(VerifierSpec("evidence", "status", 200)),
            WotExecutor(send=send),
        ).run(TaskEnvelope("wot-run", "turn on local fixture device"))
    )

    assert result.status == RuntimeStep.DONE
    assert result.result == {"surface": "wot"}


def test_same_generalist_planner_port_binds_dom_visual_and_wot_affordances() -> None:
    dom = DomAdapter().transduce(
        "<button id='enable'>Enable shared state</button>",
        environment_revision="rev-dom",
        snapshot_id="snap-1",
    ).affordances[0]
    visual = SomAdapter().parse(
        [{"bbox": [10, 10, 20, 20], "label": "Enable shared state"}],
        environment_revision="rev-visual",
        snapshot_id="snap-visual",
    )[0]
    wot = WotAdapter().parse(
        {"id": "lamp", "base": "http://fixture", "actions": {"setEnabled": {"forms": [{"href": "/on"}]}}},
        environment_revision="rev-wot",
        snapshot_id="snap-wot",
    ).affordances[0]
    model = GeneralistSurfaceModel()

    def run(affordance: Affordance, executor: Any, verifier: VerifierSpec) -> RuntimeStep:
        task = TaskSpec(
            task_id=f"generalist-{affordance.surface.value}",
            revision=1,
            objective="Enable shared state",
            operation_class=OperationClass.REVERSIBLE_WRITE,
            targets=("shared-state",),
            success_criteria=("shared state enabled",),
            requested_capabilities=("shared.write",),
            source_request_ref="surface-test",
        )
        requirements = ContractRequirements(
            verifier_plan=(verifier,),
            required_capabilities=("shared.write",),
            risk=RiskLevel.MEDIUM,
            idempotency_key=f"shared-{affordance.surface.value}",
            compensation="disable shared state",
        )
        result = asyncio.run(
            RunCoordinator(
                StaticObserver(affordance),
                GeneralistLMPlanner(model),
                executor,
                contract_builder=ContractBuilder(requirements={affordance.id: requirements}),
            ).run(TaskEnvelope(task_spec=task, capabilities=["shared.write"]))
        )
        events = [node.kind for node in result.trace.nodes]
        assert "PlannerProposalValidated" in events
        assert "PlannerProposalProduced" in events
        assert "ContractBuilt" in events
        planner_context = next(node for node in result.trace.nodes if node.kind == "PlannerContextBuilt")
        assert planner_context.payload["planner_profile"] == "strict-generalist"
        assert "semantic_compiler" not in planner_context.payload
        assert result.status == RuntimeStep.DONE, result.error_code
        return result.status

    assert run(dom, EvidenceExecutor("dom", {"action": "dom_click"}), VerifierSpec("evidence", "action", "dom_click")) == RuntimeStep.DONE
    assert run(visual, VisualExecutor(Pointer()), VerifierSpec("evidence", "action", "visual_click")) == RuntimeStep.DONE
    assert run(wot, WotExecutor(send=lambda *args, **kwargs: (200, {})), VerifierSpec("evidence", "status", 200)) == RuntimeStep.DONE
