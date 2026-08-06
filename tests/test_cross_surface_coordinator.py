import asyncio
from dataclasses import dataclass, replace
from typing import Any

from affordance_runtime.action_contract_builder import ActionContractMaterializer as ContractBuilder
from affordance_runtime.adapters.dom import DomAdapter, PageAffordanceModel
from affordance_runtime.adapters.som import SomAdapter
from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import (
    ActionContract,
    Affordance,
    ExecutionReceipt,
    Observation,
    RiskLevel,
    Surface,
    VerifierSpec,
)
from affordance_runtime.executors import VisualExecutor, WotExecutor
from affordance_runtime.planning import (
    ContractRequirements,
)
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.verification.contracts import SuccessExpression


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
            metadata=({"image_width": 100, "image_height": 100} if affordance.surface.value == "visual" else {}),
        )
        model = PageAffordanceModel("surface", "", revision, snapshot_id, page_revision, [affordance], 1, 1)
        self.snapshot = BrowserSnapshot(observation, model)

    def capture(self) -> BrowserSnapshot:
        return self.snapshot


class Pointer:
    def click_xy(self, x: int, y: int) -> None:
        self.last_click = (x, y)

    def type_text(self, text: str) -> None:
        self.last_text = text


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


def _surface_task(task_id: str, objective: str, *, target: str | None = None) -> RunRequest:
    return RunRequest(
        task_spec=TaskSpec(
            task_id=task_id,
            revision=1,
            objective=objective,
            operation_class=OperationClass.READ_ONLY,
            requirements=canonical_effect_requirements(
                (target or objective,), OperationClass.READ_ONLY, "cross-surface-test", ()
            ),
            allowed_effect_refs=canonical_effect_requirement_refs((target or objective,)),
            success=SuccessExpression(
                expression_id="success:action-verified",
                operator="criterion",
                criterion_id="criterion:action-verified",
            ),
            source_request_ref="cross-surface-test",
        )
    )


def test_visual_affordance_uses_task_coordinator_contract_trace_path() -> None:
    affordance = SomAdapter().parse(
        [{"bbox": [10, 10, 20, 20], "label": "Target"}],
        environment_revision="rev-1",
        snapshot_id="snap-1",
    )[0]
    result = asyncio.run(
        compose_run_coordinator(
            StaticObserver(affordance),
            VisualExecutor(Pointer()),
            contract_builder=ContractBuilder(
                requirements={
                    affordance.id: ContractRequirements(
                        verifier_plan=(
                            VerifierSpec(
                                "evidence",
                                "action",
                                "visual_click",
                                criterion_ids=("criterion:action-verified",),
                            ),
                        )
                    )
                }
            ),
        ).run(_surface_task("visual-run", "click visual target", target="Target"))
    )

    assert result.status == RuntimeStep.FAILED
    assert result.result == {}
    assert "TaskCompleted" not in [node.kind for node in result.trace.nodes]
    assert "PostActionEvaluated" in [node.kind for node in result.trace.nodes]


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
        compose_run_coordinator(
            StaticObserver(affordance),
            WotExecutor(send=send),
            contract_builder=ContractBuilder(
                requirements={
                    affordance.id: ContractRequirements(
                        verifier_plan=(
                            VerifierSpec(
                                "evidence",
                                "status",
                                200,
                                criterion_ids=("criterion:action-verified",),
                            ),
                        ),
                        idempotency_key="fixture-wot-action",
                    )
                }
            ),
        ).run(
            _surface_task(
                "wot-run",
                "turn on local fixture device",
                target="turn_on",
            )
        )
    )

    assert result.status == RuntimeStep.FAILED
    assert result.result == {}
    assert "TaskCompleted" not in [node.kind for node in result.trace.nodes]


def test_same_canonical_choice_flow_binds_dom_visual_and_wot_affordances() -> None:
    dom = (
        DomAdapter()
        .transduce(
            "<button id='enable'>Enable shared state</button>",
            environment_revision="rev-dom",
            snapshot_id="snap-1",
        )
        .affordances[0]
    )
    visual = SomAdapter().parse(
        [{"bbox": [10, 10, 20, 20], "label": "Enable shared state"}],
        environment_revision="rev-visual",
        snapshot_id="snap-visual",
    )[0]
    wot = (
        WotAdapter()
        .parse(
            {"id": "lamp", "base": "http://fixture", "actions": {"setEnabled": {"forms": [{"href": "/on"}]}}},
            environment_revision="rev-wot",
            snapshot_id="snap-wot",
        )
        .affordances[0]
    )

    def run(affordance: Affordance, executor: Any, verifier: VerifierSpec) -> RuntimeStep:
        verifier = replace(
            verifier,
            criterion_ids=("criterion:shared-state-enabled",),
        )
        task = TaskSpec(
            task_id=f"generalist-{affordance.surface.value}",
            revision=1,
            objective="Enable shared state",
            operation_class=OperationClass.REVERSIBLE_WRITE,
            requirements=canonical_effect_requirements(
                (affordance.label,), OperationClass.REVERSIBLE_WRITE, "surface-test", ("shared.write",)
            ),
            allowed_effect_refs=canonical_effect_requirement_refs((affordance.label,)),
            success=SuccessExpression(
                expression_id="success:shared-state-enabled",
                operator="criterion",
                criterion_id="criterion:shared-state-enabled",
            ),
            capability_ceiling=("shared.write",),
            evidence_requirements=(
                "visual appearance"
                if affordance.surface == Surface.VISUAL
                else "device property"
                if affordance.surface == Surface.WOT
                else "structural text",
            ),
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
            compose_run_coordinator(
                StaticObserver(affordance),
                executor,
                contract_builder=ContractBuilder(requirements={affordance.id: requirements}),
            ).run(RunRequest(task_spec=task, capabilities=["shared.write"]))
        )
        events = [node.kind for node in result.trace.nodes]
        assert "ActionChoiceCatalogBuilt" in events
        assert "ActionChoiceSelected" in events
        assert "ContractBuilt" in events
        assert result.status == RuntimeStep.FAILED, result.error_code
        return result.status

    assert (
        run(dom, EvidenceExecutor("dom", {"action": "dom_click"}), VerifierSpec("evidence", "action", "dom_click"))
        == RuntimeStep.FAILED
    )
    assert (
        run(visual, VisualExecutor(Pointer()), VerifierSpec("evidence", "action", "visual_click")) == RuntimeStep.FAILED
    )
    assert (
        run(wot, WotExecutor(send=lambda *args, **kwargs: (200, {})), VerifierSpec("evidence", "status", 200))
        == RuntimeStep.FAILED
    )
