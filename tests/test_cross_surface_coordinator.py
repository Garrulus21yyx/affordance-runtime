import asyncio
import json
from dataclasses import dataclass, replace
from typing import Any, Sequence, TypeVar

from pydantic import BaseModel

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
from affordance_runtime.generalist_planner import GeneralistLMPlanner, GeneralistPlannerProfile
from affordance_runtime.model_port import ModelCallRecord, ModelConfig, ModelMessage
from affordance_runtime.planning import (
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
)
from affordance_runtime.planning_contracts import (
    PlannerDoneResponse,
    PlannerProposalResponse,
)
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.runtime import RunRequest, RuntimeStep
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.verification.contracts import SuccessExpression

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
            metadata=(
                {"image_width": 100, "image_height": 100}
                if affordance.surface.value == "visual"
                else {}
            ),
        )
        model = PageAffordanceModel("surface", "", revision, snapshot_id, page_revision, [affordance], 1, 1)
        self.snapshot = BrowserSnapshot(observation, model)

    def capture(self) -> BrowserSnapshot:
        return self.snapshot


@dataclass
class OneActionPlanner:
    verifier: VerifierSpec

    def propose(
        self, request: PlanningRequest
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        affordance = request.observation.affordances[0]
        if request.recent_outcomes:
            return PlannerDoneResponse(result={"surface": affordance.surface})
        action = (
            PlannerActionKind.POINT_ACTIVATE
            if "point_activate" in affordance.supported_actions
            else PlannerActionKind.ACTIVATE
        )
        return PlannerProposalResponse(
            proposal=PlannerProposal(
                proposal_id="cross-surface-action",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal="exercise shared contract path",
                action_kind=action,
                target_affordance_id=affordance.target_id,
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="cross-surface-test",
            ),
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
            "parameters": {},
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


def _surface_task(
    task_id: str, objective: str, *, target: str | None = None
) -> RunRequest:
    return RunRequest(
        task_spec=TaskSpec(
            task_id=task_id,
            revision=1,
            objective=objective,
            operation_class=OperationClass.READ_ONLY,
            targets=(target or objective,),
            success_criteria=("action verified",),
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
            OneActionPlanner(
                VerifierSpec(
                    "evidence",
                    "action",
                    "visual_click",
                    criterion_ids=("criterion:action-verified",),
                )
            ),
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
            task_planner=None,
        ).run(_surface_task("visual-run", "click visual target"))
    )

    assert result.status == RuntimeStep.FAILED
    assert result.result == {"surface": "visual"}
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
            OneActionPlanner(
                VerifierSpec(
                    "evidence",
                    "status",
                    200,
                    criterion_ids=("criterion:action-verified",),
                )
            ),
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
            task_planner=None,
        ).run(
            _surface_task(
                "wot-run",
                "turn on local fixture device",
                target="turn_on",
            )
        )
    )

    assert result.status == RuntimeStep.FAILED
    assert result.result == {"surface": "wot"}
    assert "TaskCompleted" not in [node.kind for node in result.trace.nodes]


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
        verifier = replace(
            verifier,
            criterion_ids=("criterion:shared-state-enabled",),
        )
        task = TaskSpec(
            task_id=f"generalist-{affordance.surface.value}",
            revision=1,
            objective="Enable shared state",
            operation_class=OperationClass.REVERSIBLE_WRITE,
            targets=("shared-state",),
            success_criteria=("shared state enabled",),
            success=SuccessExpression(
                expression_id="success:shared-state-enabled",
                operator="criterion",
                criterion_id="criterion:shared-state-enabled",
            ),
            requested_capabilities=("shared.write",),
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
                GeneralistLMPlanner(
                    model,
                    planner_profile=GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY,
                ),
                    executor,
                    contract_builder=ContractBuilder(requirements={affordance.id: requirements}),
                    task_planner=None,
                ).run(RunRequest(task_spec=task, capabilities=["shared.write"]))
        )
        events = [node.kind for node in result.trace.nodes]
        assert "PlannerProposalValidated" in events
        assert "PlannerProposalProduced" in events
        assert "ContractBuilt" in events
        validated = next(node for node in result.trace.nodes if node.kind == "PlannerProposalValidated")
        assert validated.payload["provenance"]["profile_id"] == "historical-compatibility"
        assert "semantic_compiler" not in validated.payload
        assert result.status == RuntimeStep.FAILED, result.error_code
        return result.status

    assert run(dom, EvidenceExecutor("dom", {"action": "dom_click"}), VerifierSpec("evidence", "action", "dom_click")) == RuntimeStep.FAILED
    assert run(visual, VisualExecutor(Pointer()), VerifierSpec("evidence", "action", "visual_click")) == RuntimeStep.FAILED
    assert run(wot, WotExecutor(send=lambda *args, **kwargs: (200, {})), VerifierSpec("evidence", "status", 200)) == RuntimeStep.FAILED
