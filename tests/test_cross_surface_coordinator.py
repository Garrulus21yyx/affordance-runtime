import asyncio
from dataclasses import dataclass, replace
from typing import Any

from affordance_runtime.adapters.dom import PageAffordanceModel
from affordance_runtime.adapters.som import SomAdapter
from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, Affordance, Observation, VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.executors import VisualExecutor, WotExecutor
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel


class StaticObserver:
    def __init__(self, affordance: Affordance) -> None:
        observation = Observation(
            "rev-1",
            snapshot_id="snap-1",
            page_revision="rev-1",
            target_fingerprints={affordance.id: affordance.target_fingerprint},
        )
        model = PageAffordanceModel("surface", "", "rev-1", "snap-1", "rev-1", [affordance], 1, 1)
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
