from dataclasses import dataclass, replace

from affordance_runtime.action_contract_builder import ActionContractMaterializer as ContractBuilder
from affordance_runtime.adapters.dom import DomAdapter, PageAffordanceModel
from affordance_runtime.adapters.wot import WotAdapter
from affordance_runtime.approval_contracts import ConfiguredApprovalProvider
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.composition import compose_run_coordinator
from affordance_runtime.contracts import Observation, ProgressEvidenceScope, VerifierSpec
from affordance_runtime.effect_authority_contracts import (
    EffectAuthorizationScope,
    EffectClass,
    Externality,
    ResourceScopeRef,
    Reversibility,
)
from affordance_runtime.executors import ExecutorRouter, WotExecutor
from affordance_runtime.grounding import GroundingSource, SourceObservation
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
from affordance_runtime.runtime import RuntimeStep, legacy_run_request
from affordance_runtime.task_intake import (
    OperationClass,
    TaskRequirement,
    TaskSemanticPayload,
    TaskSpec,
    canonical_effect_requirement_refs,
)
from affordance_runtime.unified_grounding import (
    CandidateDescriptor,
    SemanticEntityResolver,
    candidate_fingerprints,
    candidate_from_affordance,
)
from affordance_runtime.verification.contracts import SuccessExpression

TEST_PROPOSAL_PROVENANCE = PlannerProposalProvenance(
    source=PlannerProposalSource.DETERMINISTIC_RULE,
    producer_id="authoritative-device-test-planner",
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
        wot = replace(
            (
            WotAdapter()
            .parse(
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
            )
            .affordances[0]
            ),
            operation_ref="resource.update@v1",
            effect_class=EffectClass.UPDATE.value,
            externality=Externality.PHYSICAL_WORLD.value,
            reversibility=Reversibility.REVERSIBLE.value,
            resource_sensitivity="moderate",
            authority_source_assurance="authoritative",
            risk_asserted=True,
        )
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
            CandidateDescriptor("control", "Power", "activate", "lamp", item) for item in candidates
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
        request: PlanningRequest,
    ) -> PlannerProposalResponse | PlannerDoneResponse:
        if request.recent_outcomes:
            return PlannerDoneResponse(result={"power": True})
        return PlannerProposalResponse(
            proposal_provenance=TEST_PROPOSAL_PROVENANCE,
            proposal=PlannerProposal(
                proposal_id=f"device-{request.identity.evaluated_at_state_version}",
                based_on_task_revision=request.identity.task_revision,
                based_on_state_version=request.identity.evaluated_at_state_version,
                snapshot_id=request.identity.snapshot_id,
                subgoal="Turn on the authoritative device property",
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=request.observation.affordances[0].target_id,
            ),
        )


def test_authoritative_wot_candidate_outranks_simultaneous_gui_route() -> None:
    world = DeviceWorld()
    observer = DeviceObserver(world)
    executors = ExecutorRouter()
    executors.register(WotExecutor(send=lambda method, url, **kwargs: _turn_on(world, method, url, kwargs)))
    task = TaskSpec(
        task_id="authoritative-device-route",
        revision=1,
        objective="Turn on the authoritative device property",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=(
            TaskRequirement(
                requirement_id="requirement:effect:1",
                payload=TaskSemanticPayload(
                    kind="effect",
                    subject="Power",
                    target_identity=observer.semantic_target_id,
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    capability="device.write",
                    effect_authorization_scope=EffectAuthorizationScope(
                        requirement_ref="requirement:effect:1",
                        effect_class=EffectClass.UPDATE,
                        resource_scope=ResourceScopeRef(observer.semantic_target_id, ("test",)),
                        operation_constraint="resource.update@v1",
                        externality=Externality.PHYSICAL_WORLD,
                        reversibility=Reversibility.REVERSIBLE,
                        required_capabilities=frozenset({"device.write"}),
                    ),
                ),
                source_anchor_refs=("test",),
            ),
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("Power",)),
        success=SuccessExpression(
            expression_id="success:device-power",
            operator="criterion",
            criterion_id="criterion:device-power",
            requirement_refs=("requirement:effect:1",),
        ),
        capability_ceiling=("device.write",),
        source_request_ref="test",
    )
    result = compose_run_coordinator(
        observer,
        executors,
        approval_provider=ConfiguredApprovalProvider("test-user", {"device.write"}),
        contract_builder=ContractBuilder(
            requirements={
                observer.semantic_target_id: ContractRequirements(
                    verifier_plan=(
                        VerifierSpec(
                            "observation_metadata",
                            "power",
                            True,
                            criterion_ids=("criterion:device-power",),
                            progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
                        ),
                    ),
                    idempotency_key="device:lamp:power:on",
                )
            }
        ),
    ).run_sync(legacy_run_request(task_spec=task, capabilities=["device.write"]))

    assert result.status == RuntimeStep.DONE
    assert world.power is True
    assert result.verification is not None and result.verification.passed
    route = next(node for node in result.trace.nodes if node.kind == "RouteSelected")
    assert route.payload["source"] == GroundingSource.WOT.value
    dom_gate = next(item for item in route.payload["hard_gates"] if item["candidate_id"].startswith("candidate:dom:"))
    assert dom_gate["passed"] is False
    assert "source_not_acceptable" in dom_gate["reasons"]
    approval_events = {
        node.kind: node
        for node in result.trace.nodes
        if node.kind in {"HumanApprovalRequested", "HumanApprovalGranted", "ApprovalStateRevalidated"}
    }
    assert set(approval_events) == {
        "HumanApprovalRequested",
        "HumanApprovalGranted",
        "ApprovalStateRevalidated",
    }
    assert len(
        {
            (
                event.payload["snapshot_id"],
                event.payload["page_revision"],
                event.payload["environment_revision"],
            )
            for event in approval_events.values()
        }
    ) == 1


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
