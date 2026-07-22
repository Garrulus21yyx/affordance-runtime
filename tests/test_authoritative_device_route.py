from dataclasses import dataclass, replace

from affordance_runtime.adapters.dom import DomAdapter, PageAffordanceModel
from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Observation, VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.executors import ExecutorRouter, WotExecutor
from affordance_runtime.grounding import GroundingSource, SourceObservation
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
)
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)


@dataclass
class DeviceWorld:
    power: bool = False


class DeviceObserver:
    def __init__(self, world: DeviceWorld) -> None:
        self.world = world
        self.sequence = 0
        self.semantic_target_id = self._snapshot(0).unified_affordances[0].semantic_target_id

    def capture(self) -> BrowserSnapshot:
        self.sequence += 1
        return self._snapshot(self.sequence)

    def _snapshot(self, sequence: int) -> BrowserSnapshot:
        snapshot_id = f"device-snapshot-{sequence}"
        environment_revision = f"power:{self.world.power}"
        page_revision = "device-page-v1"
        dom_model = DomAdapter().transduce(
            '<button id="power">Power</button>',
            environment_revision=environment_revision,
            snapshot_id=snapshot_id,
            page_revision=page_revision,
            ttl_ms=60_000,
        )
        dom = replace(dom_model.affordances[0], backend_candidates=["dom"])
        wot = WotAdapter().parse(
            {
                "id": "lamp",
                "base": "http://fixture",
                "actions": {
                    "power": {
                        "forms": [{"href": "/power", "op": "invokeaction"}],
                    }
                },
            },
            environment_revision=environment_revision,
            snapshot_id=snapshot_id,
            page_revision=page_revision,
            ttl_ms=60_000,
        ).affordances[0]
        observation = Observation(
            environment_revision,
            snapshot_id=snapshot_id,
            page_revision=page_revision,
            metadata={"power": self.world.power},
        )
        candidates = (
            candidate_from_affordance(
                dom,
                observation,
                semantic_target_id="pending",
                compatible_executor="dom",
            ),
            candidate_from_affordance(
                wot,
                observation,
                semantic_target_id="pending",
                compatible_executor="wot",
            ),
        )
        target = SemanticEntityResolver().resolve(
            CandidateDescriptor("control", "Power", "activate", "lamp", item)
            for item in candidates
        )[0]
        observation = replace(
            observation,
            target_fingerprints=candidate_fingerprints((target,)),
        )
        return BrowserSnapshot(
            observation,
            PageAffordanceModel(
                "device",
                "",
                environment_revision,
                snapshot_id,
                page_revision,
                [dom, wot],
                2,
                2,
            ),
            source_observations=(
                SourceObservation(
                    GroundingSource.DOM,
                    "dom-adapter",
                    snapshot_id,
                    environment_revision,
                    page_revision,
                ),
                SourceObservation(
                    GroundingSource.WOT,
                    "wot-td",
                    snapshot_id,
                    environment_revision,
                    page_revision,
                ),
            ),
            grounding_candidates=target.grounding_candidates,
            unified_affordances=(target,),
        )


class DevicePlanner:
    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        if snapshot.observation.metadata["power"] is True:
            return PlannerDecision(done=True, result={"power": True})
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id=f"device-{state.version}",
                based_on_task_revision=envelope.task_spec.revision if envelope.task_spec else 1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                subgoal="Turn on the authoritative device property",
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=snapshot.unified_affordances[0].semantic_target_id,
            )
        )


def test_authoritative_wot_candidate_outranks_simultaneous_gui_route() -> None:
    world = DeviceWorld()
    observer = DeviceObserver(world)
    executors = ExecutorRouter()
    executors.register(
        WotExecutor(send=lambda method, url, **kwargs: _turn_on(world, method, url, kwargs))
    )
    task = TaskSpec(
        task_id="authoritative-device-route",
        revision=1,
        objective="Turn on the authoritative device property",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("Power",),
        success_criteria=("device power is true",),
        evidence_requirements=("authoritative device state",),
        requested_capabilities=("device.write",),
        source_request_ref="test",
    )
    result = RunCoordinator(
        observer,
        DevicePlanner(),
        executors,
        contract_builder=ContractBuilder(
            requirements={
                observer.semantic_target_id: ContractRequirements(
                    verifier_plan=(VerifierSpec("observation_metadata", "power", True),),
                    idempotency_key="device:lamp:power:on",
                )
            }
        ),
    ).run_sync(TaskEnvelope(task_spec=task, capabilities=["device.write"]))

    assert result.status == RuntimeStep.DONE
    assert world.power is True
    assert result.verification is not None and result.verification.passed
    route = next(node for node in result.trace.nodes if node.kind == "RouteSelected")
    assert route.payload["source"] == GroundingSource.WOT.value
    dom_gate = next(
        item
        for item in route.payload["hard_gates"]
        if item["candidate_id"].startswith("candidate:dom:")
    )
    assert dom_gate["passed"] is False
    assert "source_not_acceptable" in dom_gate["reasons"]


def _turn_on(
    world: DeviceWorld,
    method: str,
    url: str,
    kwargs: dict[str, object],
) -> tuple[int, dict[str, bool]]:
    del kwargs
    assert method == "POST"
    assert url == "http://fixture/power"
    world.power = True
    return 200, {"power": True}
